"use client";

import { useId, useState } from "react";
import { ChevronDown, ChevronRight, ChevronsRight, Layers } from "lucide-react";
import {
  AgainDrawerControlBar,
  AgainDrawerLayout,
  AgainDrawerPanel,
  AgainDrawerScrollBody,
  AGAIN_DRAWER_FIELD_SHEET_CLASS,
  AGAIN_DRAWER_MODULE_LABEL_CLASS,
  AGAIN_DRAWER_RECORD_LABEL_CLASS,
} from "@/components/again/again-drawer";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { sectionLabel, type ExcellentLayoutBlock } from "@/lib/website/excellent-home";

const CHROME_SECTIONS: { id: string; label: string }[] = [
  { id: "header-top", label: "Header top" },
  { id: "header", label: "Header" },
  { id: "hero-cards", label: "Hero side cards" },
  { id: "menu", label: "Main menu" },
  { id: "footer", label: "Footer & newsletter" },
];

function SectionGroup({ title, count, expanded, onToggle, children }: { title: string; count: number; expanded: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <section className="overflow-hidden rounded-md border border-border bg-card">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex w-full items-center gap-1.5 px-2.5 py-2 text-left hover:bg-muted/40">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        <span className="min-w-0 flex-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</span>
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">{count}</span>
      </button>
      {expanded ? <div className="border-t border-border">{children}</div> : null}
    </section>
  );
}

type Props = {
  layout: ExcellentLayoutBlock[];
  selectedSection: string | null;
  pageLocked?: boolean;
  onSelect: (sectionId: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** Toolbar "Section" control: opens a drawer listing the site blocks and homepage sections; pick one to edit. */
export function LiveEditExcellentSectionPicker({ layout, selectedSection, pageLocked = false, onSelect, open, onOpenChange }: Props) {
  const titleId = useId();
  const [chromeExpanded, setChromeExpanded] = useState(true);
  const [homeExpanded, setHomeExpanded] = useState(true);

  const pick = (id: string) => {
    onOpenChange(false);
    // Let the list drawer start closing before the editor drawer opens.
    window.setTimeout(() => onSelect(id), 0);
  };

  const rowClass = (active: boolean, muted: boolean, first: boolean) =>
    cn(
      "flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-[13px] transition-colors",
      !first && "border-t border-border",
      active ? "bg-[#fdecea] font-medium text-[#d32f2f] dark:bg-[#d32f2f]/15" : muted ? "text-muted-foreground hover:bg-muted/50" : "text-foreground hover:bg-muted/50"
    );

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8 gap-1.5 px-2.5 text-[13px] text-muted-foreground"
        title="Open sections"
        aria-label="Sections"
        disabled={pageLocked}
        onClick={() => onOpenChange(true)}
      >
        <Layers className="h-3.5 w-3.5" />
        Section
      </Button>

      <AgainDrawerPanel open={open && !pageLocked} onOpenChange={onOpenChange} title="Sections" resizable defaultWidth={360} widthStorageKey="website-live-edit-sections-drawer-width">
        <AgainDrawerLayout>
          <AgainDrawerControlBar>
            <button
              type="button"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Close drawer"
              onClick={() => onOpenChange(false)}
            >
              <ChevronsRight className="h-4 w-4" />
            </button>
            <span className={AGAIN_DRAWER_MODULE_LABEL_CLASS}>Website</span>
            <span className="text-muted-foreground">/</span>
            <span className={AGAIN_DRAWER_RECORD_LABEL_CLASS} id={titleId}>
              Sections
            </span>
          </AgainDrawerControlBar>

          <AgainDrawerScrollBody className={AGAIN_DRAWER_FIELD_SHEET_CLASS}>
            <div className="space-y-3">
              <SectionGroup title="Common" count={CHROME_SECTIONS.length} expanded={chromeExpanded} onToggle={() => setChromeExpanded((v) => !v)}>
                {CHROME_SECTIONS.map((item, index) => (
                  <button key={item.id} type="button" onClick={() => pick(item.id)} className={rowClass(selectedSection === item.id, false, index === 0)}>
                    {item.label}
                  </button>
                ))}
              </SectionGroup>

              <SectionGroup title="Home sections" count={layout.length} expanded={homeExpanded} onToggle={() => setHomeExpanded((v) => !v)}>
                {layout.map((block, index) => (
                  <button key={block.id} type="button" onClick={() => pick(block.id)} className={rowClass(selectedSection === block.id, block.hidden, index === 0)}>
                    <span className="min-w-0 truncate">{sectionLabel(block.id)}</span>
                    {block.hidden ? <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">Hidden</span> : null}
                  </button>
                ))}
              </SectionGroup>
            </div>
          </AgainDrawerScrollBody>
        </AgainDrawerLayout>
      </AgainDrawerPanel>
    </>
  );
}
