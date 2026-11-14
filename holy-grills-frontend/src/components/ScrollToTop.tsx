import { useEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

const getHashId = (hash) => {
  const rawId = hash.slice(1);

  try {
    return decodeURIComponent(rawId);
  } catch {
    return rawId;
  }
};

export default function ScrollToTop() {
  const { pathname, hash, search } = useLocation();
  const navigationType = useNavigationType();

  useEffect(() => {
    // Capture ?src= order-source attribution into sessionStorage (one visit).
    try {
      const src = new URLSearchParams(search).get('src');
      if (src) sessionStorage.setItem('hg_order_source', src);
    } catch { /* ignore */ }
  }, [search]);

  useEffect(() => {
    if (navigationType === "POP") return;

    if (hash) {
      const id = getHashId(hash);
      const timer = window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
      }, 50);
      return () => window.clearTimeout(timer);
    }

    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname, hash, navigationType]);

  return null;
}