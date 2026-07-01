export type Options = {
  verbose: boolean;
};

export function greet(name: string): string {
  return `hello ${name}`;
}

// Test symbols for pruning analysis
import { someExternalFunction } from "external-lib";

export interface Config {
  debug: boolean;
}

const VERSION = "1.0.0";
let counter = 0;
var globalState: any;

export function useExternal(): void {
  // This references an external library symbol
  someExternalFunction();
}
