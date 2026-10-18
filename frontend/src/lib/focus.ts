/**
 * Moves focus back to `target` on the next frame, unless the player has meanwhile focused
 * another control outside `container` (for example the guess box right after an answer).
 */
export function restoreFocus(target: HTMLElement | null, container: HTMLElement | null): void {
  requestAnimationFrame(() => {
    const active = document.activeElement
    const idle = active === null || active === document.body || (container?.contains(active) ?? false)
    if (idle) target?.focus()
  })
}
