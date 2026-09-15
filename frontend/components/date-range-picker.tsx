"use client";

import { useEffect, useId, useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { CalendarDays, ChevronDown } from "lucide-react";
import {
  DayPicker,
  TZDate,
  useDayPicker,
  type MonthCaptionProps,
  type DateRange as CalendarRange,
} from "react-day-picker";
import { Select } from "./ui/select";
import { shiftDay } from "@/lib/api";
import "react-day-picker/style.css";
import "./date-range-picker.css";

export type DateRange = { start: string; end: string };

export function parseDate(value: string): Date | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10) === value
    ? date
    : undefined;
}

export function formatDateRange({ start, end }: DateRange) {
  const format = (value: string) => {
    const date = parseDate(value);
    return date
      ? new Intl.DateTimeFormat("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        }).format(date)
      : value;
  };
  return `${format(start)} – ${format(end)}`;
}

function CalendarCaption({
  calendarMonth,
  displayIndex,
  children: _children,
  ...props
}: MonthCaptionProps) {
  const { goToMonth, dayPickerProps } = useDayPicker();
  const date = calendarMonth.date;
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  const startYear = dayPickerProps.startMonth?.getUTCFullYear() ?? 1940;
  const endYear = dayPickerProps.endMonth?.getUTCFullYear() ?? 2100;
  const navigate = (nextYear: number, nextMonth: number) =>
    goToMonth(new TZDate(nextYear, nextMonth - displayIndex, 1, "UTC"));
  return (
    <div {...props}>
      <div className="calendar-caption-controls">
        <Select
          aria-label={`Month, calendar ${displayIndex + 1}`}
          value={month}
          onChange={(event) => navigate(year, Number(event.target.value))}
        >
          {Array.from({ length: 12 }, (_, index) => {
            const candidate = new Date(Date.UTC(year, index, 1));
            const before =
              dayPickerProps.startMonth &&
              candidate <
                new Date(
                  Date.UTC(
                    startYear,
                    dayPickerProps.startMonth.getUTCMonth(),
                    1,
                  ),
                );
            const after =
              dayPickerProps.endMonth && candidate > dayPickerProps.endMonth;
            return (
              <option key={index} value={index} disabled={!!(before || after)}>
                {new Intl.DateTimeFormat("en-GB", {
                  month: "long",
                  timeZone: "UTC",
                }).format(candidate)}
              </option>
            );
          })}
        </Select>
        <Select
          aria-label={`Year, calendar ${displayIndex + 1}`}
          value={year}
          onChange={(event) => navigate(Number(event.target.value), month)}
        >
          {Array.from({ length: endYear - startYear + 1 }, (_, index) => (
            <option key={index} value={startYear + index}>
              {startYear + index}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

export function DateRangePicker({
  value,
  onChange,
  label = "Date range",
  min,
  max,
  disabled = false,
  availableDates,
  presets = true,
  applyLabel = "Use dates",
}: {
  value: DateRange;
  onChange: (value: DateRange) => void;
  label?: string;
  min?: string;
  max?: string;
  disabled?: boolean;
  availableDates?: string[];
  presets?: boolean;
  applyLabel?: string;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const [portalContainer, setPortalContainer] = useState<
    HTMLElement | undefined
  >();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [month, setMonth] = useState(() => parseDate(value.start));
  const [compact, setCompact] = useState(false);
  const id = useId();
  useEffect(() => {
    const media = window.matchMedia("(max-width: 680px)");
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const from = parseDate(draft.start);
  const to = parseDate(draft.end);
  const error =
    !from || !to
      ? "Enter both dates as YYYY-MM-DD, or select them on the calendar."
      : draft.end < draft.start
        ? "End date must be on or after the start date."
        : (min && draft.start < min) || (max && draft.end > max)
          ? "Choose dates within the available period."
          : availableDates &&
              !availableDates.some(
                (date) => date >= draft.start && date <= draft.end,
              )
            ? "No saved forecast dates fall within this range."
            : "";
  const selected: CalendarRange | undefined = from
    ? { from, to: to && draft.end >= draft.start ? to : undefined }
    : undefined;
  const shortcuts: { label: string; range: DateRange }[] = [];
  if (presets && max && parseDate(max) && !availableDates) {
    const latest = parseDate(max)!;
    const year = latest.getUTCFullYear();
    const monthStart = `${max.slice(0, 7)}-01`;
    const nextDay = shiftDay(max, 1);
    const completeMonthEnd =
      nextDay.slice(0, 7) !== max.slice(0, 7) ? max : shiftDay(monthStart, -1);
    const fullYear = max.endsWith("12-31") ? year : year - 1;
    shortcuts.push(
      { label: "Latest 7 days", range: { start: shiftDay(max, -6), end: max } },
      {
        label: "Latest 28 days",
        range: { start: shiftDay(max, -27), end: max },
      },
      {
        label: "Latest complete month",
        range: {
          start: `${completeMonthEnd.slice(0, 7)}-01`,
          end: completeMonthEnd,
        },
      },
      {
        label: `Full year ${fullYear}`,
        range: { start: `${fullYear}-01-01`, end: `${fullYear}-12-31` },
      },
    );
  }
  function choose(range: DateRange) {
    setDraft(range);
    setMonth(parseDate(range.start));
  }
  return (
    <Popover.Root
      modal
      open={open}
      onOpenChange={(next) => {
        if (next) {
          choose(value);
          // Native modal drawers make body-level portals inert.
          setPortalContainer(trigger.current?.closest("dialog") || undefined);
        }
        setOpen(next);
      }}
    >
      <div className="date-range-field">
        <span className="date-range-label" id={`${id}-label`}>
          {label} <span>· UTC</span>
        </span>
        <Popover.Trigger asChild>
          <button
            ref={trigger}
            type="button"
            className="date-range-trigger"
            disabled={disabled}
            aria-label={`${label}: ${formatDateRange(value)}`}
          >
            <CalendarDays size={15} aria-hidden="true" />
            <span>{formatDateRange(value)}</span>
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        </Popover.Trigger>
      </div>
      <Popover.Portal container={portalContainer}>
        <Popover.Content
          className="date-range-popover"
          sideOffset={8}
          collisionPadding={12}
          align="start"
          aria-label={`Choose ${label.toLowerCase()}`}
        >
          <div className="date-range-heading">
            <strong>{label}</strong>
            <span>Both dates included · UTC</span>
          </div>
          {shortcuts.length > 0 && (
            <div className="date-range-presets" aria-label="Date shortcuts">
              {shortcuts.map((shortcut) => (
                <button
                  type="button"
                  key={shortcut.label}
                  disabled={!!min && shortcut.range.start < min}
                  aria-pressed={
                    draft.start === shortcut.range.start &&
                    draft.end === shortcut.range.end
                  }
                  onClick={() => choose(shortcut.range)}
                >
                  {shortcut.label}
                </button>
              ))}
            </div>
          )}
          <div className="date-range-inputs">
            <label htmlFor={`${id}-start`}>
              Start date
              <input
                id={`${id}-start`}
                type="text"
                inputMode="numeric"
                placeholder="YYYY-MM-DD"
                autoComplete="off"
                value={draft.start}
                aria-describedby={`${id}-help`}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    start: event.target.value,
                  }))
                }
                onBlur={() => {
                  if (from) setMonth(from);
                }}
              />
            </label>
            <span aria-hidden="true">→</span>
            <label htmlFor={`${id}-end`}>
              End date
              <input
                id={`${id}-end`}
                type="text"
                inputMode="numeric"
                placeholder="YYYY-MM-DD"
                autoComplete="off"
                value={draft.end}
                aria-describedby={`${id}-help`}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    end: event.target.value,
                  }))
                }
              />
            </label>
          </div>
          <DayPicker
            mode="range"
            timeZone="UTC"
            weekStartsOn={1}
            fixedWeeks
            numberOfMonths={compact ? 1 : 2}
            month={month}
            onMonthChange={setMonth}
            captionLayout="label"
            components={{ MonthCaption: CalendarCaption }}
            navLayout="after"
            startMonth={parseDate(min || "1940-01-01")}
            endMonth={parseDate(max || "2100-12-31")}
            selected={selected}
            onSelect={(range) =>
              setDraft({
                start: range?.from?.toISOString().slice(0, 10) || "",
                end: range?.to?.toISOString().slice(0, 10) || "",
              })
            }
            disabled={[
              ...(min ? [{ before: parseDate(min)! }] : []),
              ...(max ? [{ after: parseDate(max)! }] : []),
            ]}
            modifiers={
              availableDates
                ? {
                    saved: availableDates
                      .map(parseDate)
                      .filter((date): date is Date => !!date),
                  }
                : undefined
            }
            modifiersClassNames={{ saved: "date-range-saved" }}
          />
          <div className="date-range-help" id={`${id}-help`} aria-live="polite">
            {error ? (
              <span className="date-range-error">{error}</span>
            ) : (
              <span>
                {min && max
                  ? `Available: ${formatDateRange({ start: min, end: max })}`
                  : "Select a start and end date."}
              </span>
            )}
            {availableDates && (
              <span>
                Dots mark saved forecast dates; this range filters those
                results.
              </span>
            )}
            {shortcuts.length > 0 && (
              <span>Shortcuts use available data, not today's date.</span>
            )}
          </div>
          <div className="date-range-actions">
            <Popover.Close asChild>
              <button type="button">Cancel</button>
            </Popover.Close>
            <button
              type="button"
              className="date-range-apply"
              disabled={!!error}
              onClick={() => {
                onChange(draft);
                setOpen(false);
              }}
            >
              {applyLabel}
            </button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
