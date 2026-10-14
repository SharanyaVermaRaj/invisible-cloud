import { createContext, useContext } from "react";
import type { AppState } from "../api";

export interface AppCtx {
  state: AppState;
  refresh: () => Promise<void>;
  name: (key: string | null | undefined) => string;
}
export const Ctx = createContext<AppCtx>(null as unknown as AppCtx);
export const useApp = () => useContext(Ctx);
