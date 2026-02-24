import { Link } from 'react-router-dom';
import { Instagram, Twitter, Facebook, Youtube, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const Footer = () => {
  return (
    <footer className="bg-foreground text-background py-16">
      <div className="container mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {/* Brand */}
          <div className="space-y-4">
            <h3 className="text-2xl font-playfair font-bold">Wardo</h3>
            <p className="text-background/70 text-sm">
              Your AI-powered fashion companion. Discover your style, enhance your wardrobe, and stay ahead of trends.
            </p>
            <div className="flex space-x-4">
              <a href="#" className="text-background/70 hover:text-background transition-colors">
                <Instagram className="h-5 w-5" />
              </a>
              <a href="#" className="text-background/70 hover:text-background transition-colors">
                <Twitter className="h-5 w-5" />
              </a>
              <a href="#" className="text-background/70 hover:text-background transition-colors">
                <Facebook className="h-5 w-5" />
              </a>
              <a href="#" className="text-background/70 hover:text-background transition-colors">
                <Youtube className="h-5 w-5" />
              </a>
            </div>
          </div>

          {/* Quick Links */}
          <div className="space-y-4">
            <h4 className="font-semibold text-lg">Quick Links</h4>
            <ul className="space-y-2">
              <li>
                <Link to="/" className="text-background/70 hover:text-background transition-colors text-sm">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/style-studio" className="text-background/70 hover:text-background transition-colors text-sm">
                  Style Studio
                </Link>
              </li>
              <li>
                <Link to="/about" className="text-background/70 hover:text-background transition-colors text-sm">
                  About Us
                </Link>
              </li>
              <li>
                <Link to="/auth" className="text-background/70 hover:text-background transition-colors text-sm">
                  Sign In
                </Link>
              </li>
            </ul>
          </div>

          {/* Features */}
          <div className="space-y-4">
            <h4 className="font-semibold text-lg">Features</h4>
            <ul className="space-y-2">
              <li>
                <Link to="/style-studio/glow-up" className="text-background/70 hover:text-background transition-colors text-sm">
                  Glow Up
                </Link>
              </li>
              <li>
                <Link to="/style-studio/mix-match" className="text-background/70 hover:text-background transition-colors text-sm">
                  Mix & Match
                </Link>
              </li>
              <li>
                <Link to="/style-studio/wardrobe" className="text-background/70 hover:text-background transition-colors text-sm">
                  My Wardrobe
                </Link>
              </li>
            </ul>
          </div>

          {/* Newsletter */}
          <div className="space-y-4">
            <h4 className="font-semibold text-lg">Stay Updated</h4>
            <p className="text-background/70 text-sm">
              Subscribe to our newsletter for the latest fashion tips and updates.
            </p>
            <div className="flex space-x-2">
              <Input
                type="email"
                placeholder="Enter your email"
                className="bg-background/10 border-background/20 text-background placeholder:text-background/50"
              />
              <Button className="bg-primary hover:bg-primary/90 text-primary-foreground">
                <Mail className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-background/20 text-center text-background/50 text-sm">
          <p>&copy; {new Date().getFullYear()} Wardo. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
