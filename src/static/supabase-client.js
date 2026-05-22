// Supabase 登入 + 雲端口袋名單 client
// 公開金鑰（publishable / anon）放在前端是 Supabase 預期的用法，
// 真正的存取權限由資料表上的 Row Level Security policy 控制。
(function () {
  const SUPABASE_URL = "https://edcgdrnijwfqawhsktrq.supabase.co";
  const SUPABASE_KEY = "sb_publishable_ExcmxzGyfJVWuSdVkk_GIA_v7zxZTiy";

  if (!window.supabase || !window.supabase.createClient) {
    console.warn("Supabase JS SDK 未載入，雲端同步不可用");
    window.SB = null;
    return;
  }

  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
  });

  let currentUser = null;
  const listeners = new Set();
  const notify = () => listeners.forEach((fn) => fn(currentUser));

  sb.auth.getSession().then(({ data }) => {
    currentUser = data.session?.user || null;
    notify();
  });
  sb.auth.onAuthStateChange((_event, session) => {
    currentUser = session?.user || null;
    notify();
  });

  async function signUp(email, password) {
    const { data, error } = await sb.auth.signUp({ email, password });
    if (error) throw error;
    return data;
  }
  async function signIn(email, password) {
    const { data, error } = await sb.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
  }
  async function signOut() {
    await sb.auth.signOut();
  }

  async function cloudGetWatchlist() {
    if (!currentUser) return null;
    const { data, error } = await sb
      .from("watchlist")
      .select("code, created_at")
      .order("created_at", { ascending: true });
    if (error) throw error;
    return data.map((r) => r.code);
  }
  async function cloudSetWatchlist(codes) {
    if (!currentUser) return;
    const uid = currentUser.id;
    const { error: delErr } = await sb.from("watchlist").delete().eq("user_id", uid);
    if (delErr) throw delErr;
    if (codes.length) {
      const rows = codes.map((code) => ({ user_id: uid, code }));
      const { error: insErr } = await sb.from("watchlist").insert(rows);
      if (insErr) throw insErr;
    }
  }

  window.SB = {
    getUser: () => currentUser,
    onAuth: (fn) => {
      listeners.add(fn);
      fn(currentUser);
      return () => listeners.delete(fn);
    },
    signUp,
    signIn,
    signOut,
    cloudGetWatchlist,
    cloudSetWatchlist,
  };
})();
