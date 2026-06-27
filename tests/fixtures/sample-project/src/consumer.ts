import { greet } from "./helper";
import { VERSION } from "./config";

export const message = greet("world") + VERSION;
