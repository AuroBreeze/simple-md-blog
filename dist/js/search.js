const root = document.body.dataset.root || ".";
const indexUrl = `${root}/search-index.json`;
const input = document.getElementById("search-input");
const results = document.getElementById("search-results");
const status = document.getElementById("search-status");

let index = [];

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function matches(post, tokens) {
  const haystack = [
    post.title || "",
    post.summary || "",
    post.date || "",
    (post.categories || []).map((cat) => cat.name).join(" "),
  ]
    .join(" ")
    .toLowerCase();

  return tokens.every((token) => haystack.includes(token));
}

function buildCard(post, index) {
  const article = document.createElement("article");
  article.className = "post-card";
  article.style.animationDelay = `${Math.min(index * 0.05, 0.3)}s`;

  const categories = (post.categories || [])
    .map(
      (cat) =>
        `<a class="chip" href="${root}/categories/${cat.slug}.html">${escapeHtml(
          cat.name
        )}</a>`
    )
    .join(" ");

  const url = `${root}/${post.url}`;
  article.innerHTML = `
    <div class="post-meta">
      <span class="post-date">${escapeHtml(post.date || "")}</span>
      <div class="post-tags">${categories}</div>
    </div>
    <h2 class="post-title"><a href="${url}">${escapeHtml(post.title || "")}</a></h2>
    <p class="post-summary">${escapeHtml(post.summary || "")}</p>
    <a class="post-more" href="${url}">Read more</a>
  `;

  return article;
}

function render(list) {
  results.innerHTML = "";
  if (!list.length) {
    const empty = document.createElement("article");
    empty.className = "post-card";
    empty.innerHTML = '<p class="post-summary">No results found.</p>';
    results.appendChild(empty);
    return;
  }

  list.forEach((post, idx) => {
    results.appendChild(buildCard(post, idx));
  });
}

fetch(indexUrl)
  .then((response) => response.json())
  .then((data) => {
    index = data;
    status.textContent = `Loaded ${index.length} posts.`;
    render(index);
  })
  .catch(() => {
    status.textContent = "Search index missing. Run build.py first.";
  });

input.addEventListener("input", () => {
  const query = input.value.trim().toLowerCase();
  if (!query) {
    status.textContent = `Showing all ${index.length} posts.`;
    render(index);
    return;
  }

  const tokens = query.split(/\s+/);
  const filtered = index.filter((post) => matches(post, tokens));
  status.textContent = `Found ${filtered.length} result(s) for "${query}".`;
  render(filtered);
});
