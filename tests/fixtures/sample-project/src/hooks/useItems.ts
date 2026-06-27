import cache from "../lib/cacheHelpers";

export function useItems(): void {
  cache.evictItem();
}
