// The presence orb — a living sphere whose color, turbulence, glow and sonar rings are driven by
// Jarvis's presence state. Custom GLSL: simplex-noise vertex displacement + a fresnel rim in the
// fragment shader. Uniform values are eased toward the target each frame so state changes feel
// like the same entity shifting mood, not a hard cut.

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { audioLevel } from "../lib/audioLevel";
import { orbVisual } from "../lib/presence";
import type { PresenceState } from "../lib/types";

const vertex = /* glsl */ `
  uniform float uTime;
  uniform float uTurbulence;
  varying vec3 vNormal;
  varying float vDisp;

  // Ashima simplex noise (3D)
  vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x,289.0);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
  float snoise(vec3 v){
    const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
    vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
    vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
    vec3 x1=x0-i1+1.0*C.xxx; vec3 x2=x0-i2+2.0*C.xxx; vec3 x3=x0-1.0+3.0*C.xxx;
    i=mod(i,289.0);
    vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
    float n_=1.0/7.0; vec3 ns=n_*D.wyz-D.xzx;
    vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
    vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
    vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
    vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
    vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }

  void main(){
    vNormal = normal;
    float n = snoise(normal * 1.6 + uTime * 0.35);
    n += 0.5 * snoise(normal * 3.1 - uTime * 0.22);
    vDisp = n;
    vec3 displaced = position + normal * n * uTurbulence;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
  }
`;

const fragment = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uAccent;
  uniform float uIntensity;
  varying vec3 vNormal;
  varying float vDisp;

  void main(){
    // fresnel rim — brighter at grazing angles, gives the orb a luminous shell
    vec3 viewDir = vec3(0.0, 0.0, 1.0);
    float fres = pow(1.0 - abs(dot(normalize(vNormal), viewDir)), 2.4);
    vec3 base = mix(uColor, uAccent, clamp(vDisp * 0.6 + 0.4, 0.0, 1.0));
    vec3 col = base * (0.45 + 0.55 * uIntensity) + uAccent * fres * 1.5 * uIntensity;
    float alpha = clamp(0.72 + fres * 0.6, 0.0, 1.0);
    gl_FragColor = vec4(col, alpha);
  }
`;

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function OrbMesh({ state }: { state: PresenceState }) {
  const mat = useRef<THREE.ShaderMaterial>(null);
  const group = useRef<THREE.Group>(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uTurbulence: { value: 0.1 },
      uIntensity: { value: 1 },
      uColor: { value: new THREE.Color("#2aa39b") },
      uAccent: { value: new THREE.Color("#3de0d5") },
    }),
    [],
  );

  useFrame((_, dt) => {
    const v = orbVisual(state);
    const u = uniforms;
    // Audio-reactivity (P10): live mic/TTS amplitude blooms the surface and glow — the orb's voice.
    const amp = audioLevel.value;
    u.uTime.value += dt * (v.speed + amp * 2.5);
    u.uTurbulence.value = lerp(u.uTurbulence.value, v.turbulence + amp * 0.55, 0.18);
    u.uIntensity.value = lerp(u.uIntensity.value, v.intensity + amp * 0.9, 0.18);
    (u.uColor.value as THREE.Color).lerp(new THREE.Color(v.color), 0.05);
    (u.uAccent.value as THREE.Color).lerp(new THREE.Color(v.accent), 0.05);
    if (group.current) group.current.rotation.y += dt * 0.12 * v.speed;
  });

  return (
    <group ref={group}>
      <mesh>
        <icosahedronGeometry args={[1.35, 64]} />
        <shaderMaterial
          ref={mat}
          uniforms={uniforms}
          vertexShader={vertex}
          fragmentShader={fragment}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

function SonarRings({ state }: { state: PresenceState }) {
  const refs = useRef<THREE.Mesh[]>([]);
  const phase = useRef<number[]>([0, 0.33, 0.66]);
  useFrame((_, dt) => {
    const v = orbVisual(state);
    refs.current.forEach((m, i) => {
      if (!m) return;
      if (!v.rings) {
        m.visible = false;
        return;
      }
      m.visible = true;
      phase.current[i] = (phase.current[i] + dt * 0.4) % 1;
      const p = phase.current[i];
      const s = 1.5 + p * 2.6;
      m.scale.set(s, s, s);
      const mm = m.material as THREE.MeshBasicMaterial;
      mm.opacity = (1 - p) * 0.5;
      mm.color.set(v.accent);
    });
  });
  return (
    <>
      {[0, 1, 2].map((i) => (
        <mesh
          key={i}
          // React 19 types ref callbacks as returning void|cleanup; use a block body so the
          // assignment expression isn't returned (the old arrow returned the mesh).
          ref={(el) => {
            if (el) refs.current[i] = el;
          }}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <ringGeometry args={[1.0, 1.04, 96]} />
          <meshBasicMaterial transparent opacity={0} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </>
  );
}

export function Orb({ state }: { state: PresenceState }) {
  return (
    <Canvas
      camera={{ position: [0, 0, 4.2], fov: 42 }}
      gl={{ antialias: true, alpha: true }}
      dpr={[1, 2]}
      style={{ width: "100%", height: "100%" }}
    >
      <ambientLight intensity={0.5} />
      <OrbMesh state={state} />
      <SonarRings state={state} />
    </Canvas>
  );
}
