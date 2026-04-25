import type React from 'react';
import { Outlet } from 'react-router-dom';

type ShellProps = {
  children?: React.ReactNode;
};

export const Shell: React.FC<ShellProps> = ({ children }) => {
  return (
    <div className="h-full w-full bg-background text-foreground overflow-hidden">
      <main className="h-full min-h-0 min-w-0 flex-1 overflow-hidden">
        {children ?? <Outlet />}
      </main>
    </div>
  );
};
