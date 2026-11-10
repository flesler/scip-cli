import { greet } from "./helper";
import { VERSION } from "./config";
import { postViaGateway } from "./shim/applyGateway";

export const message = greet("world") + VERSION;
export const shimTick = (): void => postViaGateway();
