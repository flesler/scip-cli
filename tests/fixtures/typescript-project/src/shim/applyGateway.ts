import gateway from "../gateway";

export function postViaGateway(): void {
  return gateway.send();
}
