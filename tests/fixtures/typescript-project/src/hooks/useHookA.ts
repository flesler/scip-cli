interface Opts {
  alpha: number;
}

export function useHookA(opts: Opts): number {
  return opts.alpha;
}
