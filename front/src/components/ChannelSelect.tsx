import { useState } from "react";

const OTHER = "__other__";

/** Channel picker: "Todos los canales" + known channels, with a fallback to type one not yet seen locally. */
export function ChannelSelect({
  id,
  value,
  knownSources,
  onChange,
}: {
  id: string;
  value: string;
  knownSources: string[];
  onChange: (value: string) => void;
}) {
  const [customMode, setCustomMode] = useState(false);

  if (customMode || (value && !knownSources.includes(value))) {
    return (
      <input
        id={id}
        type="text"
        placeholder="channel-manager-widget"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => {
          if (!value) setCustomMode(false);
        }}
      />
    );
  }

  return (
    <select
      id={id}
      value={value}
      onChange={(e) => {
        if (e.target.value === OTHER) {
          setCustomMode(true);
          onChange("");
        } else {
          onChange(e.target.value);
        }
      }}
    >
      <option value="">Todos los canales</option>
      {knownSources.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
      <option value={OTHER}>Otro (escribir)…</option>
    </select>
  );
}
