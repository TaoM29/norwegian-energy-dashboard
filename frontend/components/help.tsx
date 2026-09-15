"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import * as Popover from "@radix-ui/react-popover";
import { Info, X } from "lucide-react";
import "./help.css";

export function HelpTip({
  label,
  children,
  iconOnly = false,
}: {
  label: string;
  children: ReactNode;
  iconOnly?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [container, setContainer] = useState<HTMLElement | undefined>();
  const trigger = useRef<HTMLButtonElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  function show() {
    clearTimeout(timer.current);
    setContainer(trigger.current?.closest("dialog") || undefined);
    setOpen(true);
  }
  function leave() {
    if (!pinned) timer.current = setTimeout(() => setOpen(false), 180);
  }
  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setPinned(false);
      }}
    >
      <Popover.Trigger asChild>
        <button
          ref={trigger}
          type="button"
          className="help-trigger"
          aria-label={`About ${label}`}
          onPointerEnter={(event) => {
            if (event.pointerType === "mouse") show();
          }}
          onPointerLeave={leave}
          onFocus={show}
          onBlur={leave}
          onClick={(event) => {
            event.preventDefault();
            clearTimeout(timer.current);
            setContainer(trigger.current?.closest("dialog") || undefined);
            setPinned(!pinned);
            setOpen(!pinned);
          }}
        >
          <Info size={14} aria-hidden="true" />
          {!iconOnly && <span>{label}</span>}
        </button>
      </Popover.Trigger>
      <Popover.Portal container={container}>
        <Popover.Content
          className="help-popover"
          sideOffset={8}
          collisionPadding={12}
          aria-label={label}
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onPointerEnter={() => clearTimeout(timer.current)}
          onPointerLeave={leave}
          onFocusCapture={() => clearTimeout(timer.current)}
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) leave();
          }}
        >
          <strong>{label}</strong>
          <div>{children}</div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function HelpPanel({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  return (
    <>
      <button
        type="button"
        className="help-trigger"
        onClick={() => dialog.current?.showModal()}
      >
        <Info size={14} aria-hidden="true" />
        {label}
      </button>
      <dialog ref={dialog} className="help-panel" aria-labelledby={title}>
        <header>
          <h2 id={title}>{label}</h2>
          <button
            type="button"
            aria-label={`Close ${label}`}
            onClick={() => dialog.current?.close()}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="help-panel-body">{children}</div>
      </dialog>
    </>
  );
}
