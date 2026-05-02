import { Outlet } from "react-router-dom";

import { MobileNav } from "@/components/layout/MobileNav";
import { SideNav } from "@/components/layout/SideNav";
import { TopAppBar } from "@/components/layout/TopAppBar";

export function Layout() {
  return (
    <div className="flex h-screen bg-bg-base text-ink">
      <SideNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopAppBar />
        <main className="flex-1 overflow-y-auto pb-20 md:pb-0 scroll-thin">
          <Outlet />
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
