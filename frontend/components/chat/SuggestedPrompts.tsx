import { GitCompareArrows, Layers, ListChecks, Sparkles } from "lucide-react";

const PROMPTS = [
  { icon: ListChecks, text: "List all features of the Hyundai Alcazar" },
  { icon: GitCompareArrows, text: "Compare the Alcazar and Creta on engine, safety, comfort and technology" },
  { icon: Layers, text: "Compare all Alcazar variants" },
  { icon: Sparkles, text: "I need a city car for a family of 4 with good mileage: i20 or Aura?" },
];

export function SuggestedPrompts({ onPick, disabled }: { onPick: (t: string) => void; disabled?: boolean }) {
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {PROMPTS.map(({ icon: Icon, text }) => (
        <button
          key={text}
          type="button"
          disabled={disabled}
          onClick={() => onPick(text)}
          className="bg-card hover:border-primary/40 hover:bg-accent/50 focus-visible:ring-ring/50 group flex items-start gap-3 rounded-xl border p-3.5 text-left text-sm shadow-xs transition outline-none focus-visible:ring-[3px] disabled:opacity-50"
        >
          <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-lg">
            <Icon className="size-4" />
          </span>
          <span className="leading-snug">{text}</span>
        </button>
      ))}
    </div>
  );
}
