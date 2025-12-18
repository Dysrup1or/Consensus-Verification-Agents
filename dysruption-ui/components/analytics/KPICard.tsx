'use client';

import { clsx } from 'clsx';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

export type KPICardProps = {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'stable';
  trendValue?: string;
  color?: 'green' | 'red' | 'yellow' | 'blue' | 'purple';
};

export default function KPICard({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendValue,
  color = 'blue',
}: KPICardProps) {
  const colorClasses = {
    green: 'bg-green-500/10 text-green-500 border-green-500/20',
    red: 'bg-red-500/10 text-red-500 border-red-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    blue: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    purple: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  };

  return (
    <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-4 hover:border-zinc-700 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-zinc-400">{title}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-xs text-zinc-500 mt-1">{subtitle}</p>}
        </div>
        <div className={clsx('p-2 rounded-lg', colorClasses[color])}>{icon}</div>
      </div>
      {trend && trendValue && (
        <div className="flex items-center mt-3 text-xs">
          {trend === 'up' && (
            <>
              <ArrowUpRight className="w-3 h-3 text-green-500 mr-1" />
              <span className="text-green-500">{trendValue}</span>
            </>
          )}
          {trend === 'down' && (
            <>
              <ArrowDownRight className="w-3 h-3 text-red-500 mr-1" />
              <span className="text-red-500">{trendValue}</span>
            </>
          )}
          {trend === 'stable' && (
            <>
              <Minus className="w-3 h-3 text-zinc-500 mr-1" />
              <span className="text-zinc-500">{trendValue}</span>
            </>
          )}
          <span className="text-zinc-500 ml-1">vs previous period</span>
        </div>
      )}
    </div>
  );
}
