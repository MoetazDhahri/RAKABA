import { createContext, useContext } from "react";

const InspectorContext = createContext({ inspectorId: "amira", displayName: "Amira", logout: () => {} });

export function InspectorProvider({ value, children }) {
  return <InspectorContext.Provider value={value}>{children}</InspectorContext.Provider>;
}

export function useInspector() {
  return useContext(InspectorContext);
}
