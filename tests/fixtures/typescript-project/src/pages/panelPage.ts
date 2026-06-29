export async function loadPanel(): Promise<unknown> {
  const mod = await import("../ui/LazyPanel");
  return mod.default;
}
