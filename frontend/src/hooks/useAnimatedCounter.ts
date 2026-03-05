import { useState, useEffect, useRef } from 'react';

/**
 * Animated counter hook for smooth number transitions
 * Provides counting animation similar to Dashboard's AnimatedStatCard
 * 
 * @param end - Target number to animate to
 * @param duration - Animation duration in milliseconds (default: 1200ms)
 * @param skip - Skip animation and show final value immediately
 * @returns Current animated count value
 * 
 * @example
 * const animatedValue = useAnimatedCounter(totalCount, 1200, isLoading);
 * return <span>{animatedValue.toLocaleString()}</span>
 */
export const useAnimatedCounter = (end: number, duration: number = 1200, skip?: boolean): number => {
  const [count, setCount] = useState(0);
  const countRef = useRef(0);
  const startTimeRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    // Cleanup any running animation
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    
    if (skip) {
      setCount(end);
      countRef.current = end;
      return;
    }
    
    const startValue = countRef.current;
    const difference = end - startValue;
    
    // Skip animation if no change
    if (difference === 0) return;
    
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      const progress = Math.min((timestamp - startTimeRef.current) / duration, 1);
      
      // Easing function for smooth animation (ease-out-quart)
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      const currentValue = Math.round(startValue + difference * easeOutQuart);
      
      setCount(currentValue);
      countRef.current = currentValue;
      
      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animate);
      } else {
        animationFrameRef.current = null;
      }
    };
    
    startTimeRef.current = null;
    animationFrameRef.current = requestAnimationFrame(animate);
    
    // Cleanup on unmount or when dependencies change
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [end, duration, skip]);

  return count;
};

export default useAnimatedCounter;
