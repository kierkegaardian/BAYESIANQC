import type { StreamCatalogOut } from "./contracts";
import { api } from "./client";

let streamCatalogPromise: Promise<StreamCatalogOut[]> | null = null;

export function loadStreamCatalog(force = false): Promise<StreamCatalogOut[]> {
  if (force || streamCatalogPromise === null) {
    streamCatalogPromise = api.get<StreamCatalogOut[]>("/stream-catalog").catch((error: unknown) => {
      streamCatalogPromise = null;
      throw error;
    });
  }
  return streamCatalogPromise;
}

export function clearStreamCatalog(): void {
  streamCatalogPromise = null;
}
