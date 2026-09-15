"use client";

import {
  Children,
  isValidElement,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import * as Primitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import "./select.css";

type Option = { value: string; label: string; disabled?: boolean };
function text(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? text(child.props.children)
        : String(child),
    )
    .join("");
}
function optionsFrom(children: ReactNode): Option[] {
  return Children.toArray(children).flatMap((child) => {
    if (
      !isValidElement<{
        value?: string | number;
        children?: ReactNode;
        disabled?: boolean;
      }>(child)
    )
      return [];
    if (child.type !== "option") return optionsFrom(child.props.children);
    const label = text(child.props.children);
    return [
      {
        value: String(child.props.value ?? label),
        label,
        disabled: child.props.disabled,
      },
    ];
  });
}

export function Select({
  value,
  onChange,
  children,
  disabled,
  id,
  name,
  required,
  className = "",
  "aria-label": label,
  "aria-labelledby": labelledBy,
  title,
}: {
  value?: string | number;
  onChange?: (event: { target: { value: string } }) => void;
  children: ReactNode;
  disabled?: boolean;
  id?: string;
  name?: string;
  required?: boolean;
  className?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  title?: string;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const [container, setContainer] = useState<HTMLElement | undefined>();
  const empty = `empty-${useId()}`;
  const options = optionsFrom(children);
  const selected = String(value ?? "");
  return (
    <Primitive.Root
      value={selected || empty}
      onValueChange={(next) =>
        onChange?.({ target: { value: next === empty ? "" : next } })
      }
      disabled={disabled}
      name={name}
      required={required}
      onOpenChange={(open) => {
        if (open) setContainer(trigger.current?.closest("dialog") || undefined);
      }}
    >
      <Primitive.Trigger
        ref={trigger}
        data-value={selected}
        id={id}
        className={`modern-select ${className}`}
        aria-label={label}
        aria-labelledby={labelledBy}
        title={title}
      >
        <Primitive.Value>
          {options.find((option) => option.value === selected)?.label ||
            "Choose…"}
        </Primitive.Value>
        <Primitive.Icon>
          <ChevronDown size={15} aria-hidden="true" />
        </Primitive.Icon>
      </Primitive.Trigger>
      <Primitive.Portal container={container}>
        <Primitive.Content
          className="select-content"
          position="popper"
          sideOffset={6}
          collisionPadding={12}
        >
          <Primitive.ScrollUpButton className="select-scroll">
            <ChevronUp size={14} />
          </Primitive.ScrollUpButton>
          <Primitive.Viewport className="select-options">
            {options.map((option) => (
              <Primitive.Item
                key={option.value}
                data-value={option.value}
                value={option.value || empty}
                disabled={option.disabled}
                className="select-option"
                textValue={option.label}
              >
                <Primitive.ItemText>{option.label}</Primitive.ItemText>
                <Primitive.ItemIndicator>
                  <Check size={15} aria-hidden="true" />
                </Primitive.ItemIndicator>
              </Primitive.Item>
            ))}
          </Primitive.Viewport>
          <Primitive.ScrollDownButton className="select-scroll">
            <ChevronDown size={14} />
          </Primitive.ScrollDownButton>
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}
