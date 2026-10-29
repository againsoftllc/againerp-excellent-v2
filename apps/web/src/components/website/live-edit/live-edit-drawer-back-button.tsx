"use client";

import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  onBack: () => void;
  disabled?: boolean;
  className?: string;
  label?: string;
};

/** Shared Back control for live-edit drawers (returns to Sections list). */
export function LiveEditDrawerBackButton({
  onBack,
  disabled = false,
  className,
  label = "Back",
}: Props) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn(
        "h-8 gap-1 px-2 text-[13px] text-muted-foreground hover:text-foreground",
        className,
      )}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onBack}
    >
      <ChevronLeft className="h-4 w-4" />
      {label}
    </Button>
  );
}
