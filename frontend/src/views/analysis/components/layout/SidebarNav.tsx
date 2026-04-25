import React from 'react';
import { BarChart3 } from 'lucide-react';
import { cn } from '../../utils/cn';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
};

export const SidebarNav: React.FC<SidebarNavProps> = ({ collapsed = false }) => {
  return (
    <div className="flex h-full flex-col">
      <div className={cn('mb-4 flex items-center gap-2 px-1', collapsed ? 'justify-center' : '')}>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-gradient text-[hsl(var(--primary-foreground))] shadow-[0_12px_28px_var(--nav-brand-shadow)]">
          <BarChart3 className="h-5 w-5" />
        </div>
        {!collapsed ? (
          <p className="min-w-0 truncate text-sm font-semibold text-foreground">DSA</p>
        ) : null}
      </div>

      <nav className="flex flex-1 flex-col gap-1.5" aria-label="Main Navigation" />

      <div className="mt-4 mb-2">
        <ThemeToggle variant="nav" collapsed={collapsed} />
      </div>
    </div>
  );
};
