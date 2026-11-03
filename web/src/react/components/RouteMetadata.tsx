import { useEffect } from "react";
import type { ViewKey } from "../types";

const publicMetadata: Partial<Record<ViewKey, { title: string; description: string; path: string }>> = {
  home: {
    title: "Planora | Academic Timetabling and Scheduling",
    description: "Planora helps university teams build academic timetables, manage scheduling constraints, review conflicts, and publish approved schedules.",
    path: "/",
  },
  faq: {
    title: "Planora FAQ | Academic Timetabling",
    description: "Find answers about Planora's academic scheduling, user roles, organizations, and privacy choices.",
    path: "/faq",
  },
  privacy: {
    title: "Privacy | Planora Academic Scheduling",
    description: "Read about Planora's scheduling data, essential cookies, optional analytics, and account communications.",
    path: "/privacy",
  },
};

export function RouteMetadata({ view }: { view: ViewKey }) {
  useEffect(() => {
    const page = publicMetadata[view];
    document.title = page?.title ?? "Planora | Sign in and workspace";
    const description = document.head.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = page?.description ?? "Sign in to the Planora academic scheduling workspace.";
    let robots = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!robots) {
      robots = document.createElement("meta");
      robots.name = "robots";
      document.head.append(robots);
    }
    robots.content = page ? "index,follow" : "noindex,follow";
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!page) {
      canonical?.remove();
      return;
    }
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = `https://planora.elfeel.me${page.path}`;
  }, [view]);

  return null;
}
