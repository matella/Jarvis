import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Artifact } from "../lib/types";
import { ArtifactRenderer } from "./ArtifactRenderer";

describe("ArtifactRenderer", () => {
  it("renders a table artifact with headers and cells", () => {
    const a: Artifact = {
      kind: "table",
      title: "Containers",
      data: { columns: ["name", "status"], rows: [["nginx", "running"], ["redis", "exited"]] },
    };
    render(<ArtifactRenderer artifact={a} />);
    expect(screen.getByText("Containers")).toBeInTheDocument();
    expect(screen.getByText("nginx")).toBeInTheDocument();
    expect(screen.getByText("exited")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table")).toBeInTheDocument();
  });

  it("renders a status_grid with status text", () => {
    const a: Artifact = {
      kind: "status_grid",
      title: "Services",
      data: { items: [{ label: "gpu", status: "high" }, { label: "db", status: "running" }] },
    };
    render(<ArtifactRenderer artifact={a} />);
    expect(screen.getByText("gpu")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("renders markdown bold and inline code", () => {
    const a: Artifact = {
      kind: "markdown",
      title: "Note",
      data: { text: "restart **nginx** via `docker.restart_container`" },
    };
    render(<ArtifactRenderer artifact={a} />);
    expect(screen.getByText("nginx").tagName).toBe("STRONG");
    expect(screen.getByText("docker.restart_container").tagName).toBe("CODE");
  });

  it("falls back to JSON for an unknown artifact kind", () => {
    const a: Artifact = { kind: "mystery", title: "Raw", data: { a: 1 } };
    render(<ArtifactRenderer artifact={a} />);
    expect(screen.getByTestId("artifact-mystery")).toBeInTheDocument();
    expect(screen.getByText(/"a": 1/)).toBeInTheDocument();
  });
});
