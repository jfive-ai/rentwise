import { createRoot } from "react-dom/client";
import { Popup } from "./Popup";

const el = document.getElementById("root");
if (el) createRoot(el).render(<Popup />);
