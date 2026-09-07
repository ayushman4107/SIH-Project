import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">404</h1>
      <p className="text-lg text-gray-600 mb-8">Page not found.</p>
      <Link to="/" className="text-purple-600 hover:text-purple-800 underline font-medium">
        Return Home
      </Link>
    </div>
  );
}
