interface StatCardProps {
  label: string;
  value: number;
  accent: string;
}

export function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <section className="stat-card">
      <span className="stat-card__accent" style={{ background: accent }} />
      <p className="stat-card__label">{label}</p>
      <strong className="stat-card__value">{value}</strong>
    </section>
  );
}

