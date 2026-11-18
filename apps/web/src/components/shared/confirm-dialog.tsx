"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/**
 * The ONE confirmation popup of the admin. Never use `window.confirm` (the browser's own box, "localhost says…").
 *
 *   if (!(await confirmDialog("Remove this product from the offer?"))) return;
 *   if (!(await confirmDialog({ title: "Delete role", message: "Delete “Sales”?", confirmLabel: "Delete", danger: true }))) return;
 *
 * `<ConfirmHost />` is mounted once in AppProviders; it draws the popup that these calls open.
 */
export type ConfirmOptions = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button (delete / remove). Default: guessed from the words delete/remove/discard in the message. */
  danger?: boolean;
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

let show: ((p: Pending) => void) | null = null;

export function confirmDialog(input: string | ConfirmOptions): Promise<boolean> {
  const opts = typeof input === "string" ? { message: input } : input;
  return new Promise<boolean>((resolve) => {
    // no host mounted (should not happen in the admin): fall back to the browser box instead of silently doing nothing
    if (!show) return resolve(typeof window !== "undefined" ? window.confirm(opts.message) : false);
    show({ ...opts, resolve });
  });
}

export function ConfirmHost() {
  const [queue, setQueue] = useState<Pending[]>([]);
  useEffect(() => {
    show = (p) => setQueue((q) => [...q, p]);
    return () => {
      show = null;
    };
  }, []);
  const current = queue[0];
  const close = (ok: boolean) => {
    current?.resolve(ok);
    setQueue((q) => q.slice(1));
  };
  const danger = current ? (current.danger ?? /\b(delete|remove|discard|cancel this)\b/i.test(current.message)) : false;
  return (
    <Dialog.Root open={!!current} onOpenChange={(o) => { if (!o) close(false); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[200] bg-black/40" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-[201] w-[400px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 space-y-3 border border-border bg-background p-4 shadow-lg focus:outline-none"
          onOpenAutoFocus={(e) => {
            // focus the confirm button so Enter confirms and Esc cancels
            e.preventDefault();
            (e.currentTarget as HTMLElement).querySelector<HTMLButtonElement>("[data-confirm]")?.focus();
          }}
        >
          <Dialog.Title className="text-sm font-semibold">{current?.title ?? "Please confirm"}</Dialog.Title>
          <Dialog.Description className="whitespace-pre-line text-xs text-muted-foreground">{current?.message}</Dialog.Description>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" size="sm" className="rounded-none" onClick={() => close(false)}>
              {current?.cancelLabel ?? "Cancel"}
            </Button>
            <Button data-confirm size="sm" variant={danger ? "destructive" : "default"} className="rounded-none" onClick={() => close(true)}>
              {current?.confirmLabel ?? (danger ? "Remove" : "OK")}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
