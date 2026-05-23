import React from 'react';

type SectionCardProps = {
  title: string;
  icon?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
};

export const SectionCard: React.FC<SectionCardProps> = ({
  title,
  icon,
  right,
  children,
  className = 'min-w-0 rounded-2xl border border-slate-800 bg-slate-900/70 shadow-lg',
  headerClassName = 'flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3',
  bodyClassName = 'p-4',
}) => (
  <section className={className}>
    <div className={headerClassName}>
      <div className="flex items-center gap-2 text-sm font-semibold text-white">
        {icon}
        <span>{title}</span>
      </div>
      {right}
    </div>
    <div className={bodyClassName}>{children}</div>
  </section>
);

type MetricProps = {
  label: string;
  value: string;
  tone?: string;
  className?: string;
  valueClassName?: string;
};

export const Metric: React.FC<MetricProps> = ({
  label,
  value,
  tone = 'text-slate-100',
  className = 'min-w-0 rounded-xl border border-slate-800 bg-slate-950/45 p-3',
  valueClassName = 'mt-1 break-words text-sm font-semibold',
}) => (
  <div className={className}>
    <div className="text-[11px] text-slate-500">{label}</div>
    <div className={`${valueClassName} ${tone}`}>{value}</div>
  </div>
);
