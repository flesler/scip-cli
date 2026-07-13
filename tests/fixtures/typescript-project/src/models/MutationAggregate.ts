/** Repeated aggregate fields (Prisma-style) + a real ErrorCode type. */
export type ErrorCode = "NONE" | "FAILED";

export type MutationMinAggregate = {
  id: string | null;
  errorCode: string | null;
};

export type MutationMaxAggregate = {
  id: string | null;
  errorCode: string | null;
};

export type MutationCountAggregate = {
  id: string | null;
  errorCode: string | null;
};

export type MutationAvgAggregate = {
  id: string | null;
  errorCode: string | null;
};

export type MutationSumAggregate = {
  id: string | null;
  errorCode: string | null;
};

export type MutationGroupByAggregate = {
  id: string | null;
  errorCode: string | null;
};
