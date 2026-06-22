import React, { useRef, useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

interface ClaimNode {
  id: string;
  label: string;
  group?: number;
  val?: number; // node size
  details?: {
    page?: number;
    metric?: string;
    value?: number;
    year?: string;
    text?: string;
  };
}

interface ClaimLink {
  source: string;
  target: string;
  type: string;
  severity?: string;
}

interface ClaimGraphProps {
  data: {
    nodes: ClaimNode[];
    links: ClaimLink[];
  };
  onNodeClick?: (node: ClaimNode) => void;
  width?: number;
  height?: number;
}

const ClaimGraph: React.FC<ClaimGraphProps> = ({ data, onNodeClick, width, height }) => {
  const fgRef = useRef<any>();
  const [dimensions, setDimensions] = useState({ width: width || 800, height: height || 400 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!width || !height) {
      const updateDimensions = () => {
        if (containerRef.current) {
          setDimensions({
            width: containerRef.current.clientWidth,
            height: height || 400
          });
        }
      };
      
      window.addEventListener('resize', updateDimensions);
      updateDimensions();
      
      return () => window.removeEventListener('resize', updateDimensions);
    }
  }, [width, height]);

  // Center the graph on load
  useEffect(() => {
    if (fgRef.current && data.nodes.length > 0) {
      // Small timeout ensures the graph has rendered
      setTimeout(() => {
        fgRef.current.zoomToFit(400, 50);
      }, 500);
    }
  }, [data]);

  return (
    <div 
      ref={containerRef} 
      className="w-full h-full rounded-lg overflow-hidden relative"
    >
      <div className="absolute top-2 right-2 z-10 bg-background/80 p-2 rounded border border-border/50 text-xs text-muted-foreground pointer-events-none shadow-sm backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-danger"></div> Critical Conflict</div>
        <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-warning"></div> Temporal/Scope</div>
        <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-success"></div> Entailment</div>
      </div>
      
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeLabel={(node: any) => {
          // Powerful Hover Evidence Tooltip
          const d = node.details;
          if (!d) return node.label;
          return `
            <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255,255,255,0.1); padding: 8px; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); color: #f8fafc; font-family: sans-serif; max-width: 250px; backdrop-filter: blur(8px);">
              <div style="font-weight: bold; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; color: #38bdf8;">Page ${d.page || '?'}</div>
              <div style="font-size: 11px; margin-bottom: 2px;"><b>Metric:</b> ${d.metric || 'N/A'}</div>
              <div style="font-size: 11px; margin-bottom: 6px;"><b>Value:</b> <span style="color: #4ade80;">${d.value || 'N/A'}</span> ${d.year ? `<span style="color: #94a3b8;">(${d.year})</span>` : ''}</div>
              <div style="font-size: 11px; color: #94a3b8; font-style: italic;">"${node.label}"</div>
            </div>
          `;
        }}
        nodeColor={(node: any) => node.group === 1 ? '#0ea5e9' : '#64748b'}
        nodeRelSize={6}
        linkColor={(link: any) => {
          if (link.type === 'contradiction' && link.severity === 'Critical') return '#ef4444'; // Red
          if (link.type === 'contradiction') return '#f59e0b'; // Amber
          return '#64748b'; // Gray for neutral/entailed
        }}
        linkWidth={(link: any) => link.type === 'contradiction' ? 2 : 1}
        linkDirectionalParticles={(link: any) => link.type === 'contradiction' ? 2 : 0}
        linkDirectionalParticleSpeed={0.005}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        onNodeClick={(node: any) => {
          if (onNodeClick) onNodeClick(node);
          
          // Center on clicked node
          if (fgRef.current) {
            fgRef.current.centerAt(node.x, node.y, 1000);
            fgRef.current.zoom(4, 2000);
          }
        }}
        backgroundColor="rgba(0,0,0,0)"
      />
    </div>
  );
};

export default ClaimGraph;
