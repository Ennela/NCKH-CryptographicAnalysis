"use client";

import { useEffect, useState } from "react";

export default function AdminPage() {
    const [health, setHealth] = useState<any>(null);
    const [models, setModels] = useState<any[]>([]);
    const [jobs, setJobs] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchAdminData = async () => {
            try {
                const headers = { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" };

                // Fetch 3 API song song
                const [healthRes, modelsRes, jobsRes] = await Promise.all([
                    fetch("http://localhost:8000/health"),
                    fetch("http://localhost:8000/api/v1/models", { headers }),
                    fetch("http://localhost:8000/api/v1/jobs", { headers })
                ]);

                if (healthRes.ok) setHealth(await healthRes.json());
                if (modelsRes.ok) setModels(await modelsRes.json());
                if (jobsRes.ok) setJobs(await jobsRes.json());
            } catch (error) {
                console.error("Lỗi khi tải dữ liệu:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchAdminData();
    }, []);

    if (loading) return <div className="p-8 text-slate-300">Đang tải dữ liệu...</div>;

    return (
        <div className="p-8 min-h-screen bg-slate-900 text-slate-200">
            <h1 className="text-3xl font-bold mb-8 text-blue-400">Trang Quản Trị & Log</h1>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                {/* Khối Health */}
                <div className="bg-slate-800 p-6 rounded-xl border border-slate-700">
                    <h2 className="text-xl font-semibold mb-4 text-emerald-400">Trạng thái API (/health)</h2>
                    <pre className="bg-slate-950 p-4 rounded-lg overflow-x-auto text-sm text-slate-300">
                        {JSON.stringify(health, null, 2)}
                    </pre>
                </div>

                {/* Khối Models */}
                <div className="bg-slate-800 p-6 rounded-xl border border-slate-700">
                    <h2 className="text-xl font-semibold mb-4 text-purple-400">Mô hình đã đăng ký</h2>
                    <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                        {models.length > 0 ? (
                            models.map((m, idx) => (
                                <li key={idx}>
                                    <span className="font-mono text-blue-300">{m.model_name}</span> (v{m.version}) - {m.status}
                                </li>
                            ))
                        ) : (<li>Chưa có mô hình nào</li>)}
                    </ul>
                </div>
            </div>

            {/* Khối Jobs */}
            <div className="bg-slate-800 p-6 rounded-xl border border-slate-700">
                <h2 className="text-xl font-semibold mb-4 text-orange-400">Nhật ký Job Thu thập (ops.job_log)</h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm border-collapse">
                        <thead className="bg-slate-900 text-slate-400 border-b border-slate-700">
                            <tr>
                                <th className="p-3">Thời gian</th>
                                <th className="p-3">Loại Job</th>
                                <th className="p-3">Mã Tài Sản</th>
                                <th className="p-3">Thời gian chạy</th>
                                <th className="p-3">Trạng thái</th>
                                <th className="p-3">Lỗi</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-700">
                            {jobs.length > 0 ? jobs.map((job, idx) => (
                                <tr key={idx} className="hover:bg-slate-750">
                                    <td className="p-3 text-slate-400">{new Date(job.time).toLocaleString('vi-VN')}</td>
                                    <td className="p-3">{job.job_type}</td>
                                    <td className="p-3 font-mono text-blue-300">{job.symbol_id}</td>
                                    <td className="p-3">{job.duration_ms} ms</td>
                                    <td className="p-3">
                                        <span className={`px-2 py-1 rounded text-xs ${job.status === 'succeeded' ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/50 text-red-400'}`}>
                                            {job.status}
                                        </span>
                                    </td>
                                    <td className="p-3 text-red-400">{job.error || '-'}</td>
                                </tr>
                            )) : (
                                <tr><td colSpan={6} className="p-8 text-center">Chưa có dữ liệu job log.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}