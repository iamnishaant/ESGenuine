import { motion } from 'framer-motion';
import { Calendar, Play, Pause } from 'lucide-react';
import { useState } from 'react';

export const TimelineSlider = () => {
  const [value, setValue] = useState(75);
  const [isPlaying, setIsPlaying] = useState(false);
  const months = ['Jan', 'Apr', 'Jul', 'Oct', 'Dec'];

  return (
    <motion.div 
      className="glass-panel p-4"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
    >
      <div className="flex items-center gap-4">
        <motion.button
          className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center hover:bg-primary/30 transition-colors"
          onClick={() => setIsPlaying(!isPlaying)}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
        >
          {isPlaying ? (
            <Pause className="w-4 h-4 text-primary" />
          ) : (
            <Play className="w-4 h-4 text-primary ml-0.5" />
          )}
        </motion.button>
        
        <div className="flex-1 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" />
              Temporal Analysis: 2024
            </span>
            <span className="text-xs font-mono text-primary">
              {Math.round(value / 100 * 12)} months
            </span>
          </div>
          
          <div className="relative h-2 bg-muted rounded-full overflow-hidden">
            {/* Tick marks */}
            <div className="absolute inset-0 flex justify-between px-1">
              {[...Array(12)].map((_, i) => (
                <div 
                  key={i} 
                  className="w-px h-full bg-border/50"
                />
              ))}
            </div>
            
            {/* Progress */}
            <motion.div
              className="absolute h-full rounded-full bg-gradient-to-r from-primary to-primary/70"
              style={{ width: `${value}%` }}
              initial={{ width: 0 }}
              animate={{ width: `${value}%` }}
              transition={{ duration: 0.3 }}
            >
              <div className="absolute inset-0 shimmer" />
            </motion.div>
            
            {/* Scrubber handle */}
            <motion.div
              className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-primary glow-primary cursor-grab"
              style={{ left: `calc(${value}% - 8px)` }}
              whileHover={{ scale: 1.2 }}
              drag="x"
              dragConstraints={{ left: 0, right: 0 }}
              dragElastic={0}
              onDrag={(_, info) => {
                const parent = info.point.x;
                // Simplified drag handling
              }}
            />
            
            {/* Input overlay for interaction */}
            <input
              type="range"
              min="0"
              max="100"
              value={value}
              onChange={(e) => setValue(Number(e.target.value))}
              className="absolute inset-0 w-full opacity-0 cursor-pointer"
            />
          </div>
          
          <div className="flex justify-between px-1">
            {months.map((month) => (
              <span key={month} className="text-[10px] text-muted-foreground">
                {month}
              </span>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
};
