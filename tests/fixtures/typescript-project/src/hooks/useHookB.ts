interface Opts {
  beta: number;
}

export function useHookB(opts: Opts): number {
  return opts.beta;
}
