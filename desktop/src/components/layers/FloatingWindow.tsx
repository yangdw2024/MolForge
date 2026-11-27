import React, { useEffect, useRef, useState } from "react";
import { GripHorizontal, Minus, Square, X } from "lucide-react";

// 全局递增 z 计数：最后交互的浮窗永远在最上层
let nextFloatingZ = 40;

interface FloatingWindowProps {
  id: string;
  title: string;
  icon?: React.ReactNode;
  initialPos?: { x: number; y: number };
  initialSize?: { width: number; height: number };
  minWidth?: number;
  minHeight?: number;
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  headerExtra?: React.ReactNode;
}

export const FloatingWindow: React.FC<FloatingWindowProps> = ({
  title,
  icon,
  initialPos = { x: 80, y: 80 },
  initialSize = { width: 440, height: 480 },
  minWidth = 320,
  minHeight = 240,
  isOpen,
  onClose,
  children,
  headerExtra,
}) => {
  const [pos, setPos] = useState(initialPos);
  const [size, setSize] = useState(initialSize);
  const [isMinimized, setIsMinimized] = useState(false);
  const [zIndex, setZIndex] = useState(30);

  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null);

  // 每次打开都提升到最上层（hook 必须在早退之前无条件调用）
  useEffect(() => {
    if (isOpen) setZIndex(nextFloatingZ++);
  }, [isOpen]);

  if (!isOpen) return null;

  const bringToFront = () => {
    setZIndex(nextFloatingZ++);
  };

  const handleDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    bringToFront();
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: pos.x,
      origY: pos.y,
    };

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.startX;
      const dy = ev.clientY - dragRef.current.startY;
      setPos({
        x: Math.max(10, Math.min(window.innerWidth - 100, dragRef.current.origX + dx)),
        y: Math.max(40, Math.min(window.innerHeight - 80, dragRef.current.origY + dy)),
      });
    };

    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    bringToFront();
    resizeRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origW: size.width,
      origH: size.height,
    };

    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const dw = ev.clientX - resizeRef.current.startX;
      const dh = ev.clientY - resizeRef.current.startY;
      setSize({
        width: Math.max(minWidth, resizeRef.current.origW + dw),
        height: Math.max(minHeight, resizeRef.current.origH + dh),
      });
    };

    const onUp = () => {
      resizeRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <div
      onMouseDown={bringToFront}
      className="absolute flex flex-col rounded-2xl border backdrop-blur-2xl overflow-hidden select-none transition-all duration-75 shadow-2xl"
      style={{
        left: pos.x,
        top: pos.y,
        width: isMinimized ? 240 : size.width,
        height: isMinimized ? 38 : size.height,
        zIndex,
        backgroundColor: "color-mix(in srgb, var(--bg-secondary) 88%, transparent)",
        borderColor: "var(--border-subtle)",
        boxShadow: "0 24px 60px rgba(0, 0, 0, 0.45)",
      }}
    >
      {/* Title Bar / Drag Handle */}
      <div
        onMouseDown={handleDragStart}
        className="h-[38px] shrink-0 px-3 flex items-center justify-between border-b cursor-grab active:cursor-grabbing"
        style={{ borderColor: "var(--border-subtle)", backgroundColor: "color-mix(in srgb, var(--bg-primary) 50%, transparent)" }}
      >
        <div className="flex items-center gap-2 text-[12px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>
          <GripHorizontal size={14} style={{ color: "var(--text-muted)" }} />
          {icon}
          <span className="truncate">{title}</span>
        </div>

        <div className="flex items-center gap-1.5" onMouseDown={(e) => e.stopPropagation()}>
          {headerExtra}
          <button
            type="button"
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1 rounded hover:bg-[var(--bg-tertiary)] cursor-pointer"
            style={{ color: "var(--text-muted)" }}
            title={isMinimized ? "展开" : "最小化"}
          >
            {isMinimized ? <Square size={11} /> : <Minus size={11} />}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--semantic-error)] hover:text-white cursor-pointer"
            style={{ color: "var(--text-muted)" }}
            title="关闭图层"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      {/* Body */}
      {!isMinimized && (
        <div className="flex-1 min-h-0 overflow-auto select-text flex flex-col">
          {children}
        </div>
      )}

      {/* Resize Handle */}
      {!isMinimized && (
        <div
          onMouseDown={handleResizeStart}
          className="absolute right-0 bottom-0 w-3 h-3 cursor-nwse-resize z-20 hover:bg-[var(--accent-primary)]/40 transition-colors"
        />
      )}
    </div>
  );
};
