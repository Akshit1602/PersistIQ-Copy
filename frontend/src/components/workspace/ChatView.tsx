import React from 'react';
import { type UIArtifactCard } from '../../context/ConversationalLoopContext';
import { InteractiveEvaluationCard } from '../chat/InteractiveEvaluationCard';
import { PowerEvaluationCard } from '../chat/PowerEvaluationCard';
import { BriefHandoffCard } from '../chat/BriefHandoffCard';

export const ArtifactCardRenderer: React.FC<{ card: UIArtifactCard }> = ({ card }) => {
  const type = card.type?.toLowerCase() || '';
  const payload = (card.payload || {}) as any;

  if (type.includes('srm') || type.includes('stat_results') || type.includes('interactive')) {
    return <InteractiveEvaluationCard {...payload} title={card.title} />;
  }

  if (type.includes('power') || type.includes('sample_size')) {
    return <PowerEvaluationCard {...payload} title={card.title} />;
  }

  if (type.includes('brief') || type.includes('handoff')) {
    return <BriefHandoffCard {...payload} title={card.title} />;
  }

  // Generic fallback for custom cards / charts
  return (
    <div className="p-4 my-2 border rounded-lg bg-slate-900/50 border-slate-800 text-slate-200">
      <h4 className="font-semibold text-sm mb-2 text-indigo-400">{card.title}</h4>
      <pre className="text-xs overflow-x-auto p-2 bg-slate-950 rounded text-emerald-400">
        {JSON.stringify(card.payload, null, 2)}
      </pre>
    </div>
  );
};