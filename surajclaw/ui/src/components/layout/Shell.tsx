import { Outlet } from "react-router-dom";

import { MobileNav } from "./MobileNav";
import { SideNav } from "./SideNav";
import { TopAppBar } from "./TopAppBar";

export function Shell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <SideNav />
      <div className="flex-1 flex flex-col min-w-0">
        <TopAppBar />
        <main className="flex-1 overflow-y-auto scroll-thin pb-20 md:pb-0">
          <Outlet />
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
