import client from "../integrations/inferenceClient";

export function useInference(): number {
  return client.run();
}
