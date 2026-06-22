import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export const CursorGlow = () => {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setPosition({ x: e.clientX, y: e.clientY });
      setIsVisible(true);
    };

    const handleMouseLeave = () => setIsVisible(false);
    const handleMouseEnter = () => setIsVisible(true);

    window.addEventListener('mousemove', handleMouseMove);
    document.body.addEventListener('mouseleave', handleMouseLeave);
    document.body.addEventListener('mouseenter', handleMouseEnter);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      document.body.removeEventListener('mouseleave', handleMouseLeave);
      document.body.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, []);

  return (
    <motion.div
      className="pointer-events-none fixed z-50"
      animate={{
        x: position.x - 150,
        y: position.y - 150,
        opacity: isVisible ? 1 : 0,
      }}
      transition={{
        type: 'spring',
        stiffness: 500,
        damping: 28,
        mass: 0.5,
      }}
    >
      <div className="relative w-[300px] h-[300px]">
        {/* Main glow */}
        <div className="absolute inset-0 rounded-full bg-gradient-radial from-primary/10 via-primary/5 to-transparent" />
        {/* Inner bright spot */}
        <div className="absolute inset-[100px] rounded-full bg-gradient-radial from-primary/20 to-transparent blur-md" />
      </div>
    </motion.div>
  );
};
