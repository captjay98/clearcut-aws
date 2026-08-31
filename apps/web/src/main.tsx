import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { RootQueryProvider, queryClient } from "./integrations/tanstack-query/root-provider";
import { createRouter } from "./router";
import "./index.css";

const router = createRouter();

const rootElement = document.getElementById("root");
if (rootElement && !rootElement.innerHTML) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <RootQueryProvider>
        <RouterProvider router={router} context={{ queryClient }} />
      </RootQueryProvider>
    </React.StrictMode>
  );
}
