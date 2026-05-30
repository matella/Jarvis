// Cmd-K command palette — fast keyboard navigation/actions. Pure frontend; each command is a
// callback the app wires (switch surface, focus chat, jump to a tab). Opens on ⌘K / Ctrl-K.

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

export function useCommandPalette(): { open: boolean; setOpen: (v: boolean) => void } {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}

export function CommandPalette({
  open,
  setOpen,
  commands,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  commands: Command[];
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands;
  }, [query, commands]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  if (!open) return null;

  const exec = (cmd: Command | undefined) => {
    if (!cmd) return;
    cmd.run();
    setOpen(false);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-[60] grid place-items-start justify-center bg-black/60 pt-[18vh]"
        onClick={() => setOpen(false)}
      >
        <motion.div
          initial={{ scale: 0.97, y: -6 }} animate={{ scale: 1, y: 0 }}
          className="bracket panel w-full max-w-lg p-2"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, filtered.length - 1));
              else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
              else if (e.key === "Enter") exec(filtered[cursor]);
            }}
            placeholder="Type a command…"
            className="w-full bg-transparent px-2 py-2 text-sm text-ink outline-none placeholder:text-ink-faint"
          />
          <ul className="mt-1 max-h-72 overflow-y-auto">
            {filtered.map((c, i) => (
              <li key={c.id}>
                <button
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => exec(c)}
                  className={`flex w-full items-center justify-between px-2 py-1.5 text-left text-sm ${
                    i === cursor ? "bg-teal/10 text-teal" : "text-ink"
                  }`}
                >
                  <span>{c.label}</span>
                  {c.hint && <span className="label">{c.hint}</span>}
                </button>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="px-2 py-2 text-xs text-steel">no matching command</li>
            )}
          </ul>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
