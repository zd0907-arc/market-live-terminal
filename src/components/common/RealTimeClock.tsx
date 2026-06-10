import React, { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

const RealTimeClock: React.FC = () => {
    const [time, setTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => {
            setTime(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    const formatDate = (date: Date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    const formatTime = (date: Date) => {
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    };

    return (
        <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap">
            <Clock className="h-3 w-3 shrink-0 text-slate-600" />
            <span className="inline-flex gap-x-1">
                <span>{formatDate(time)}</span>
                <span className="font-mono tabular-nums">{formatTime(time)}</span>
            </span>
        </span>
    );
};

export default RealTimeClock;
