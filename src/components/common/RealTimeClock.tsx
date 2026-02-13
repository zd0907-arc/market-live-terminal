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
        <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-slate-600" />
            <span>{formatDate(time)}</span>
            <span className="font-mono w-[60px]">{formatTime(time)}</span>
        </span>
    );
};

export default RealTimeClock;