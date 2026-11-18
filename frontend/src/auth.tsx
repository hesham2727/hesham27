import { createContext, useContext } from "react";
import type { User } from "./api";

export interface AuthState {
  user: User | null;
  setUser: (u: User | null) => void;
}

export const AuthContext = createContext<AuthState>({ user: null, setUser: () => undefined });
export const useAuth = () => useContext(AuthContext);
