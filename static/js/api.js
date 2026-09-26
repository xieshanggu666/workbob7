const Api = {
  async request(method, url, body) {
    const opts = { method, headers: {}, credentials: "include" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (res.status === 401) {
      location.hash = "#/login";
      throw new Error("未登录或登录已失效");
    }
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) throw new Error(data.detail || res.statusText || "请求失败");
    return data;
  },
  get(url) { return this.request("GET", url); },
  post(url, body) { return this.request("POST", url, body !== undefined ? body : {}); },
};

window.StatusBadge = (s) => {
  const map = {
    draft: ["草稿", "gray"], published: ["已发布", "blue"], bidding: ["招标中", "blue"],
    announced: ["公告中", "blue"], evaluating: ["评标中", "yellow"], awarded: ["已定标", "green"],
    failed: ["流标", "red"], closed: ["已关闭", "gray"],
    pending: ["待确认", "yellow"], confirmed: ["已确认", "green"], cancelled: ["已取消", "red"],
    qualified: ["合规通过", "green"], disqualified: ["不合规", "red"], submitted: ["已提交", "gray"],
    won: ["中标", "green"], lost: ["未中标", "gray"],
    unpaid: ["未缴纳", "yellow"], paid: ["已缴纳", "green"], returned: ["已退还", "gray"], forfeited: ["已没收", "red"],
  };
  const [label, color] = map[s] || [s, "gray"];
  return `<span class="badge ${color}">${label}</span>`;
};
