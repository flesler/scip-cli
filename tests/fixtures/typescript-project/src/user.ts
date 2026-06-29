import { Widget } from "./widget";

export function useWidget(): string {
  const w = new Widget();
  return w.run();
}
