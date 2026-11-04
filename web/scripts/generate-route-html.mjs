import { mkdir, readFile, writeFile } from "node:fs/promises";
import metadata from "../src/react/pageMetadata.json" with { type: "json" };

const dist = new URL("../dist/", import.meta.url);
const template = await readFile(new URL("index.html", dist), "utf8");
const escape = (value) => value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

function render(page) {
  const title = page?.title ?? "Planora | Sign in and workspace";
  const description = page?.description ?? "Sign in to the Planora academic scheduling workspace.";
  const robots = page ? "index,follow" : "noindex,follow";
  const canonical = page ? `\n    <link rel="canonical" href="https://planora.elfeel.me${escape(page.path)}" />` : "";
  const head = `<title>${escape(title)}</title>\n    <meta name="description" content="${escape(description)}" />\n    <meta name="robots" content="${robots}" />${canonical}`;
  const pattern = /<title>[^<]*<\/title>\s*<meta name="description" content="[^"]*"\s*\/>/g;
  if ([...template.matchAll(pattern)].length !== 1) throw new Error("Expected exactly one title and description in the built HTML");
  return template.replace(pattern, () => head);
}

await mkdir(new URL("__seo/", dist), { recursive: true });
await Promise.all([
  writeFile(new URL("index.html", dist), render(metadata.home)),
  writeFile(new URL("__seo/faq.html", dist), render(metadata.faq)),
  writeFile(new URL("__seo/privacy.html", dist), render(metadata.privacy)),
  writeFile(new URL("__seo/workspace.html", dist), render(null)),
]);
