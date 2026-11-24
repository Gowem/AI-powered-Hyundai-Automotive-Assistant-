import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function Home() {
  const jar = await cookies();
  redirect(jar.get(process.env.AUTH_COOKIE_NAME ?? "hyundai_session") ? "/chat" : "/login");
}
