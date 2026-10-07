/** Browser React supplied by DSH's module loader; no bundled React copy. */
declare module 'react' {
  export function createElement(type: string | ((props: never) => unknown), props: Record<string, unknown> | null, ...children: unknown[]): unknown
  export function useState<T>(initial: T): [T, (value: T) => void]
  export function useEffect(effect: () => void | (() => void), dependencies: readonly unknown[]): void
}
