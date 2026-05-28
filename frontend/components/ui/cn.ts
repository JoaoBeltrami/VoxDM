/**
 * Utility minúscula pra concatenar classes condicionais sem depender de clsx.
 *
 * Aceita strings, undefined, null, false — ignora os falsy.
 *
 * Uso:
 *   cn("base", isOpen && "open", isPrimary ? "primary" : "secondary")
 */
export function cn(...args: Array<string | undefined | null | false>): string {
  return args.filter(Boolean).join(" ");
}
