"use client";

import { useRef, useState, type ReactNode } from "react";
import * as Popover from "@radix-ui/react-popover";
import { Download } from "lucide-react";
import "./export-menu.css";

export function ExportMenu({
  children,
  label = "Export",
}: {
  children: ReactNode;
  label?: string;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const [container, setContainer] = useState<HTMLElement | undefined>();
  return (
    <Popover.Root
      onOpenChange={(open) => {
        if (open) setContainer(trigger.current?.closest("dialog") || undefined);
      }}
    >
      <Popover.Trigger ref={trigger} className="export-trigger">
        <Download size={14} aria-hidden="true" />
        {label}
      </Popover.Trigger>
      <Popover.Portal container={container}>
        <Popover.Content
          className="export-popover"
          align="end"
          sideOffset={6}
          collisionPadding={12}
          aria-label="Export options"
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
