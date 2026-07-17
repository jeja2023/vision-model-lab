import { FileCheck2, LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { errorMessage, login, type LoginResponse } from "../api";

type LoginProps = {
  onLoggedIn: (session: LoginResponse) => void;
};

export function Login({ onLoggedIn }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username || !password || pending) {
      return;
    }
    setPending(true);
    setError("");
    try {
      const session = await login(username, password);
      onLoggedIn(session);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <FileCheck2 size={28} />
          <div>
            <strong>视觉模型研发平台</strong>
            <span>模型交付控制台</span>
          </div>
        </div>
        <label>
          <span>用户名</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
          />
        </label>
        <label>
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <div className="login-error">{error}</div> : null}
        <button className="primary-button login-submit" type="submit" disabled={pending || !username || !password}>
          <LogIn size={16} />
          {pending ? "登录中..." : "登录"}
        </button>
      </form>
    </div>
  );
}
